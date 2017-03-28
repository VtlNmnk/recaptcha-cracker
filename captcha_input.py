import splinter
import requests
from PIL import Image
import os
import glob
import nn
from preprocessors import LabelProcessor, ImagePreprocessor
import time
from nltk.corpus import wordnet as wn
from selenium.common.exceptions import StaleElementReferenceException
import uuid
import json


def find_image_url(captcha_iframe, image_checkboxes=None):
    print("Getting URLs.")

    if image_checkboxes:
        image_urls = []
        for checkbox in image_checkboxes:
            x, y = checkbox['position']
            changed_image_xpath = '//*[@id="rc-imageselect-target"]/table/tbody/tr[{0}]/td[{1}]/div/div[1]/img'\
                .format(x, y)
            if captcha_iframe.is_element_present_by_xpath(changed_image_xpath, wait_time=3):
                image_url = captcha_iframe.find_by_xpath(changed_image_xpath)['src']
                image_urls.append(image_url)
            else:
                print("can't find image")
        return image_urls
    else:
        image_xpath = '//*[@id="rc-imageselect-target"]/table/tbody/tr[1]/td[1]/div/div[1]/img'
        if captcha_iframe.is_element_present_by_xpath(image_xpath, wait_time=3):
            image_url = captcha_iframe.find_by_xpath(image_xpath)['src']
        else:
            print("can't find image")
            reload(captcha_iframe)
        return image_url


def pick_checkboxes_from_positions(positions, image_checkboxes):
    checkboxes = []
    for pos in positions:
        checkboxes.append(image_checkboxes[pos])

    return checkboxes


def get_image_checkboxes(rows, cols, captcha_iframe):
    print("Getting image checkbox elements.")
    image_checkboxes = []
    for i in range(1, rows+1):
        for j in range(1, cols+1):
            checkbox_xpath = '//*[@id="rc-imageselect-target"]/table/tbody/tr[{0}]/td[{1}]/div'.format(i, j)

            if captcha_iframe.is_element_present_by_xpath(checkbox_xpath, wait_time=3):
                image_checkboxes.append({'checkbox': captcha_iframe.find_by_xpath(checkbox_xpath), 'position': (i, j)})
            else:
                print("Can't find a checkbox at {0}, {1}".format(i, j))
    return image_checkboxes


def verify(captcha_iframe):
    print("Clicking verify.")
    if captcha_iframe.is_element_present_by_id('recaptcha-verify-button', wait_time=3):
        verify_button = captcha_iframe.find_by_id('recaptcha-verify-button')
        verify_button.first.click()

    # not_select_all_images_error = captcha_iframe.is_text_not_present('Please select all matching images.')
    # not_retry_error = captcha_iframe.is_text_not_present('Please try again.')
    # not_select_more_images_error = captcha_iframe.is_text_not_present('Please also check the new images.')
    # if not_select_all_images_error and not_retry_error and not_select_more_images_error:
    #     correct_score += 1
    # total_guesses += 1
    # print("Total possibly correct: {correct}".format(correct=correct_score))
    # print("Total guesses: {guesses}".format(guesses=total_guesses))
    # print("Percentage: {percent}".format(percent=float(correct_score)/total_guesses))


def delete_old_images():
    old_captcha_images = glob.glob('*captcha-*.jpg')
    for image in old_captcha_images:
        os.remove(os.path.join(os.path.dirname(os.path.abspath(__file__)), image))


def download_images(image_url, row_count, col_count, captcha_text, random_folder_name, image_urls=None):
    print("Downloading images.")
    if image_urls:
        delete_old_images()

        for i, url in enumerate(image_urls):
            img = Image.open(requests.get(url, stream=True).raw)
            img.save("new-captcha-{0}.jpg".format(i), "JPEG")
    else:
        img = Image.open(requests.get(image_url, stream=True).raw)
        img.save("original-captcha-image.jpg", "JPEG")

        delete_old_images()

        width = img.size[0] / col_count
        height = img.size[1] / row_count

        captcha_folder = "datasets/captchas/{0}".format(captcha_text)
        for row in range(row_count):
            for col in range(col_count):
                dimensions = (col * width, row * height, col * width + width, row * height + height)
                individual_captcha_image = img.crop(dimensions)
                individual_captcha_image.save("captcha-{0}-{1}.jpg".format(row, col), "JPEG")

                if not os.path.exists(captcha_folder):
                    os.mkdir(captcha_folder)

                if not os.path.exists(captcha_folder + "/" + random_folder_name):
                    os.mkdir("{0}/{1}".format(captcha_folder, random_folder_name))
                individual_captcha_image.save("{0}/{1}/{2}-{3}.jpg".format(captcha_folder, random_folder_name, row, col), "JPEG")


def find_rows_and_cols(captcha_iframe):
    row_count = 0
    col_count = 0
    if captcha_iframe.is_element_present_by_css('#rc-imageselect-target > table', wait_time=3):
        table = captcha_iframe.find_by_css('#rc-imageselect-target > table')
        row_count, col_count = table.first['class'].split(" ")[0].split('-')[3]
        row_count, col_count = int(row_count), int(col_count)
        print("rows from find_rows_and_cols: {0}, cols: {1}".format(row_count, col_count))
    return row_count, col_count


def get_captcha_query(captcha_iframe):
    text_xpath = '//*[@id="rc-imageselect"]/div[2]/div[1]/div[1]/div[1]/strong'
    if captcha_iframe.is_element_present_by_xpath(text_xpath, wait_time=3):
        captcha_text = captcha_iframe.find_by_xpath(text_xpath).first['innerHTML']
        return captcha_text


def pick_checkboxes_matching_query(image_checkboxes, predicted_word_labels, query):
    matching_labels = []
    for i, image_labels in enumerate(predicted_word_labels):
        for label in image_labels:
            label_synsets = wn.synsets(label, pos=wn.NOUN)
            print("wordnet labels: ", label_synsets)
            query_synsets = wn.synsets(query, pos=wn.NOUN)
            print("query synsets: ", query_synsets)
            if label_synsets and query_synsets:
                print(label_synsets, query_synsets)
                for label_synset in label_synsets:
                    for query_synset in query_synsets:
                        similarity = label_synset.path_similarity(query_synset)
                        print("similarity: ", similarity, label_synset, query_synset)
                        if similarity is not None and similarity > 0.5:
                            matching_labels.append(i) # this works if the test is == because there aren't duplicate labels
            else:
                if label == query:
                    matching_labels.append(i)
        # for i in range(len(image_labels)):
        #     if image_labels[i] == query:
        #         matching_labels.append(i * len(predicted_word_labels) + j)

    matching_image_checkboxes = pick_checkboxes_from_positions(matching_labels, image_checkboxes)
    return matching_image_checkboxes


def click_checkboxes(checkboxes):
    if checkboxes:
        for checkbox in checkboxes:
            if checkbox['checkbox'].visible:
                checkbox['checkbox'].click()


def reload(captcha_iframe):
    print("Reloading captcha iframe...")
    if captcha_iframe.is_element_present_by_id('recaptcha-reload-button', wait_time=3):
        recaptcha_reload_button = captcha_iframe.find_by_id('recaptcha-reload-button')
        recaptcha_reload_button.first.click()


def click_initial_checkbox(browser):
    with browser.get_iframe('undefined') as iframe:
        print("Clicking initial checkbox.")
        captcha_checkbox = iframe.find_by_xpath('//div[@class="recaptcha-checkbox-checkmark"]')
        captcha_checkbox.first.click()


def write_guesses_to_file(predictions, folder, captcha_text):
    with open('guesses.json','a+') as guess_file:
        existing_predictions = guess_file.read()
        if existing_predictions:
            json_predictions = json.loads(existing_predictions)
            if captcha_text not in json_predictions:
                json_predictions[captcha_text] = {}
            json_predictions[captcha_text][folder] = predictions
            guess_file.write(json.dumps(json_predictions))
        else:
            new_predictions = {}
            new_predictions[captcha_text] = {}
            new_predictions[captcha_text][folder] = predictions
            guess_file.write(json.dumps(new_predictions))


def guess_captcha(browser, neural_net, correct_score=0, total_guesses=0):

    if os.path.exists('logs/current_state.json'):
        with open('logs/current_state.json','r') as current_state_file:
            current_state = json.loads(current_state_file)
            correct_score = current_state[correct_score]
            total_guesses = current_state[total_guesses]

    # total_guesses not necessarily separate captchas, one captcha with new images added would count as two
    new_run = True
    while browser.is_element_present_by_css('body > div > div:nth-child(4) > iframe', wait_time=3):
        image_iframe = browser.find_by_css('body > div > div:nth-child(4) > iframe')
        with browser.get_iframe(image_iframe.first['name']) as captcha_iframe:
            # need to keep getting images and image urls until this batch of image urls is the same as the last run
            # i.e. keep selecting images until the captcha stops replacing images

            # if new captcha, get checkboxes, download images, pick checkboxes
            if new_run:
                random_folder_name = str(uuid.uuid4())
                picked_checkboxes = None # reinitialise picked_checkboxes so previous state doesn't cause problems
                row_count, col_count = find_rows_and_cols(captcha_iframe)

                if row_count == 0 or col_count == 0:
                    break

                total_guesses = 0
                print("New CAPTCHA.")
                image_url = find_image_url(captcha_iframe)
                captcha_text = get_captcha_query(captcha_iframe)
                captcha_text = LabelProcessor.depluralise_string(captcha_text)
                download_images(image_url, row_count, col_count, captcha_text, random_folder_name)
                ImagePreprocessor.resize_images(glob.glob('*.jpg'))
                ImagePreprocessor.colour_images(glob.glob('*.jpg'))

                labels = neural_net.predict_image_classes()
                # print(labels)
                # labels = [i for (i,probability) in labels]
                predicted_word_labels = LabelProcessor.convert_labels_to_label_names(labels)

                # predicted_word_labels = [prediction['data']['concepts'][0]['name'] for prediction in app.tag_files(glob.glob('*_110x110.jpg'))['outputs']]
                predicted_word_labels = [LabelProcessor.conflate_labels(image_labels) for image_labels in predicted_word_labels]
                # print(predicted_word_labels)


                image_checkboxes = get_image_checkboxes(row_count, col_count, captcha_iframe)
                picked_checkboxes = pick_checkboxes_matching_query(image_checkboxes, predicted_word_labels, captcha_text)

                write_guesses_to_file(predicted_word_labels, random_folder_name, captcha_text)

                if picked_checkboxes:
                    click_checkboxes(picked_checkboxes)
                    new_run = False
                    new_image_urls = find_image_url(captcha_iframe, image_checkboxes)
                else:
                    reload(captcha_iframe)
                    new_run = True

            elif any(image_url != new_image_url for new_image_url in new_image_urls):
                print("Some images have changed but CAPTCHA hasn't.")

                image_url = find_image_url(captcha_iframe)
                captcha_text = get_captcha_query(captcha_iframe)
                captcha_text = LabelProcessor.depluralise_string(captcha_text)
                download_images(image_url, row_count, col_count, captcha_text, random_folder_name, new_image_urls)
                ImagePreprocessor.resize_images(glob.glob('*.jpg'))
                ImagePreprocessor.colour_images(glob.glob('*.jpg'))

                labels = neural_net.predict_image_classes()
                predicted_word_labels = LabelProcessor.convert_labels_to_label_names(labels)
                predicted_word_labels = [LabelProcessor.conflate_labels(image_labels) for image_labels in predicted_word_labels]
                new_image_checkboxes = get_image_checkboxes(row_count, col_count, captcha_iframe)
                picked_checkboxes = pick_checkboxes_matching_query(new_image_checkboxes, predicted_word_labels, captcha_text)

                if picked_checkboxes:
                    click_checkboxes(picked_checkboxes)
                    new_image_urls = find_image_url(captcha_iframe, new_image_checkboxes)
                    new_run = False
                else:
                    verify(captcha_iframe)
                    new_run = True
            else:
                print("Not a new captcha and none of the images have changed, verifying.")
                verify(captcha_iframe)
                new_run = True

            total_guesses += 1

    outer_iframe = browser.find_by_css('body > form > div > div > div > iframe')
    with browser.get_iframe(outer_iframe.first['name']) as iframe:
        checkmarkbox = iframe.find_by_id('recaptcha-anchor')
        if checkmarkbox.has_class('recaptcha-checkbox-checked'):
            browser.reload()
            correct_score += 1
            print("Captchas Correct: {0}".format(correct_score))
            guess_captcha(browser, correct_score, total_guesses)

    if browser.is_element_not_present_by_css('body > form > div > div > div > iframe', wait_time=3):
        print("iframe isn't present and neither is correct checkbox, reloading")
        browser.reload()
        click_initial_checkbox()
        guess_captcha(browser, correct_score, total_guesses)

    current_state = {'total_guesses': total_guesses, 'correct_score': correct_score}
    with open('logs/current_state.json','a+') as f:
        f.write(json.dumps(current_state))

def start_guessing():
    with splinter.Browser() as browser:
        url = "https://nocturnaltortoise.github.io/captcha"
        browser.visit(url)
        neural_net = nn.NeuralNetwork('extra-data-model-conv-net-weights.h5')
        try:
            click_initial_checkbox(browser)

            if browser.is_element_present_by_css('body > div > div:nth-child(4) > iframe', wait_time=3):
                print("Captcha iframe is present")
                guess_captcha(browser, neural_net)
            else:
                print("Captcha iframe not present.")
                raise splinter.exceptions.ElementDoesNotExist
                # better to crash and let supervisor handle it than to reload the browser ourselves
        except StaleElementReferenceException:
            print("stale element exception, reloading")
            browser.reload()
            start_guessing() # this works but it keeps making new browser windows
        except Exception as e:
            print(e)
            browser.reload()
            start_guessing()

start_guessing()
